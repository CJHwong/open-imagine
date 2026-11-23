//! One HTTP connection carried between the WebView's socket and an iroh stream pair.
//!
//! The asker is the WebView, which sends requests. The answerer is the iroh stream to the
//! studio, which sends responses.
//!
//! When the answerer closes, nothing more can arrive, so the WebView's socket closes at once.
//! Copying the two directions with `join!` waited for the WebView to close as well, and a
//! browser keeps an idle connection open: the studio's close never reached the WebView, which
//! then sent its next request into a connection nobody read, and that request hung. When the
//! WebView closes its sending half, the studio gets the same half-close, and the forward waits
//! for the rest of the response. An error on either side ends both.

use std::io;

use tokio::io::{AsyncRead, AsyncWrite, AsyncWriteExt};

pub async fn relay<AskerRead, AskerWrite, AnswerRead, AnswerWrite>(
    mut asker_read: AskerRead,
    mut asker_write: AskerWrite,
    mut answer_read: AnswerRead,
    mut answer_write: AnswerWrite,
) -> io::Result<()>
where
    AskerRead: AsyncRead + Unpin,
    AskerWrite: AsyncWrite + Unpin,
    AnswerRead: AsyncRead + Unpin,
    AnswerWrite: AsyncWrite + Unpin,
{
    let request = async {
        tokio::io::copy(&mut asker_read, &mut answer_write).await?;
        answer_write.shutdown().await
    };
    let response = async {
        tokio::io::copy(&mut answer_read, &mut asker_write).await?;
        asker_write.shutdown().await
    };
    tokio::pin!(request, response);
    tokio::select! {
        answered = &mut response => answered,
        asked = &mut request => {
            asked?;
            response.await
        }
    }
}

#[cfg(test)]
mod tests {
    use std::time::Duration;

    use tokio::io::{duplex, AsyncReadExt, AsyncWriteExt, DuplexStream};
    use tokio::time::timeout;

    use super::relay;

    /// The relay between `asker` and `answerer`, with the two far ends the test drives.
    fn wire() -> (
        DuplexStream,
        DuplexStream,
        tokio::task::JoinHandle<std::io::Result<()>>,
    ) {
        let (asker, asker_side) = duplex(1024);
        let (answerer, answer_side) = duplex(1024);
        let (asker_read, asker_write) = tokio::io::split(asker_side);
        let (answer_read, answer_write) = tokio::io::split(answer_side);
        let task = tokio::spawn(relay(asker_read, asker_write, answer_read, answer_write));
        (asker, answerer, task)
    }

    #[tokio::test]
    async fn an_answerer_that_closes_closes_the_askers_socket_at_once() {
        let (mut asker, mut answerer, task) = wire();
        asker.write_all(b"GET / HTTP/1.1\r\n\r\n").await.unwrap();
        let mut request = [0u8; 18];
        answerer.read_exact(&mut request).await.unwrap();
        answerer
            .write_all(b"HTTP/1.1 200 OK\r\n\r\n")
            .await
            .unwrap();
        // The studio closes an idle connection. The asker has not closed and never will.
        drop(answerer);

        let mut seen = Vec::new();
        let read = timeout(Duration::from_secs(2), asker.read_to_end(&mut seen)).await;
        assert!(read.is_ok(), "the asker never saw the close");
        assert_eq!(seen, b"HTTP/1.1 200 OK\r\n\r\n");
        timeout(Duration::from_secs(2), task)
            .await
            .unwrap()
            .unwrap()
            .unwrap();
    }

    #[tokio::test]
    async fn an_asker_that_stops_sending_still_gets_the_whole_answer() {
        let (mut asker, mut answerer, task) = wire();
        asker.write_all(b"request").await.unwrap();
        asker.shutdown().await.unwrap();

        let mut request = Vec::new();
        timeout(Duration::from_secs(2), answerer.read_to_end(&mut request))
            .await
            .unwrap()
            .unwrap();
        assert_eq!(request, b"request");
        answerer.write_all(b"answer").await.unwrap();
        drop(answerer);

        let mut seen = Vec::new();
        timeout(Duration::from_secs(2), asker.read_to_end(&mut seen))
            .await
            .unwrap()
            .unwrap();
        assert_eq!(seen, b"answer");
        timeout(Duration::from_secs(2), task)
            .await
            .unwrap()
            .unwrap()
            .unwrap();
    }

    #[tokio::test]
    async fn an_asker_that_disappears_tells_the_answerer_and_the_forward_ends_with_it() {
        let (asker, mut answerer, task) = wire();
        drop(asker);

        let mut request = Vec::new();
        let told = timeout(Duration::from_secs(2), answerer.read_to_end(&mut request)).await;
        assert!(told.is_ok(), "the answerer never saw the asker leave");
        drop(answerer);
        timeout(Duration::from_secs(2), task)
            .await
            .unwrap()
            .unwrap()
            .unwrap();
    }
}
